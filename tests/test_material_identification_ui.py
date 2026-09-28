from pathlib import Path
import csv
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _FakeWidget:
    def __init__(self, parent=None, **kwargs):
        self.parent = parent
        self.kwargs = kwargs
        self.children = []
        if parent is not None and hasattr(parent, "children"):
            parent.children.append(self)

    def pack(self, **kwargs):
        self.pack_options = kwargs

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)

    def bind(self, sequence, callback, add=None):
        self.binding = (sequence, callback, add)


class _FakeNotebook(_FakeWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.children = []
        self.labels = {}

    def add(self, child, *, text):
        if child not in self.children:
            self.children.append(child)
        self.labels[child] = text

    def insert(self, index, child, *, text):
        if child in self.children:
            self.children.remove(child)
        self.children.insert(int(index), child)
        self.labels[child] = text

    def index(self, child):
        return self.children.index(child)

    def tab(self, child, option=None, **kwargs):
        if "text" in kwargs:
            self.labels[child] = kwargs["text"]
        if option == "text":
            return self.labels[child]

    def tabs(self):
        return tuple(self.children)


class _FakeTreeview(_FakeWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.headings = {}
        self.columns = {}
        self.items = {}

    def heading(self, key, **kwargs):
        self.headings[key] = kwargs

    def column(self, key, **kwargs):
        self.columns[key] = kwargs

    def yview(self, *args):
        return args

    def get_children(self):
        return tuple(self.items)

    def delete(self, *items):
        for item in items:
            self.items.pop(item, None)

    def insert(self, _parent, _index, *, values):
        item = f"item-{len(self.items) + 1}"
        self.items[item] = tuple(values)
        return item


class _FakeScrollbar(_FakeWidget):
    def set(self, *args):
        self.last_set = args


class _FakeVariable:
    def __init__(self, value=""):
        self.value = value
        self.traces = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, mode, callback):
        self.traces.append((mode, callback))
        return f"trace-{len(self.traces)}"


def _widget_texts(widget):
    texts = []
    text = widget.kwargs.get("text")
    if text:
        texts.append(text)
    for child in widget.children:
        texts.extend(_widget_texts(child))
    return texts


class MaterialIdentificationInstallerTests(unittest.TestCase):
    def _application(self):
        import material_identification_ui

        class FakeApplication:
            def __init__(self, root):
                self.root = root
                self.tabs = _FakeNotebook()
                self.project_path = None
                self.abaqus_path = _FakeVariable()
                self.experimental_path = _FakeVariable()
                self.abaqus_installation_label = _FakeVariable(
                    "No installation detected"
                )
                self._abaqus_installations = {}
                self.result = None
                self.manual_review_tab = _FakeWidget(self.tabs)
                self.details_tab = _FakeWidget(self.tabs)
                self.tabs.add(self.manual_review_tab, text="8. Manual review")
                self.tabs.add(self.details_tab, text="9. Details")

        fake_ttk = SimpleNamespace(
            Button=_FakeWidget,
            Frame=_FakeWidget,
            Label=_FakeWidget,
            LabelFrame=_FakeWidget,
            Notebook=_FakeNotebook,
            Scrollbar=_FakeScrollbar,
            Separator=_FakeWidget,
            Treeview=_FakeTreeview,
        )
        app_module = SimpleNamespace(ModalComparatorApp=FakeApplication)
        with patch.object(material_identification_ui, "_INSTALLED", False), patch.object(
            material_identification_ui, "ttk", fake_ttk
        ):
            material_identification_ui.install_material_identification_ui(app_module)
            return app_module.ModalComparatorApp(object())

    def _application_with_report_evidence(self):
        application = self._application()
        application.identified_properties = {
            "recommendation": "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
            "models": {
                "U": {"properties_MPa": {"Ex": 45.0, "Ey": 60.0, "Gxy": 8.0}},
                "P": {"properties_MPa": {"Ex": 48.0, "Ey": 59.0, "Gxy": 7.0}},
            },
            "stability": {
                "Ex": "RELATIVELY_STABLE",
                "Ey": "RELATIVELY_STABLE",
                "Gxy": "WEIGHTING_SENSITIVE",
                "U_P_symmetric_difference_percent": {
                    "Ex": 4.0,
                    "Ey": 1.0,
                    "Gxy": 17.0,
                },
            },
        }
        application.validation_evidence = {
            "recommendation": "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
            "primary_observables": (
                {
                    "model": "U",
                    "observable": "A7",
                    "experimental_frequency_hz": 31.4,
                    "fe_frequency_hz": 29.8,
                    "frequency_error_percent": -5.2,
                    "status": "PASS",
                },
            ),
            "holdouts": (
                {
                    "model": "P",
                    "observable": "A10+A11",
                    "experimental_frequency_hz": 95.45,
                    "fe_frequency_hz": 93.25,
                    "frequency_error_percent": -2.3,
                    "status": "IMPROVES",
                },
            ),
        }
        application._refresh_material_identification_pages()
        return application

    def test_tab_creation_contains_all_gui_zero_sections(self):
        from ui_policy import MATERIAL_IDENTIFICATION_STEP_LABELS

        application = self._application()
        labels = tuple(
            application.material_identification_notebook.tab(tab, "text")
            for tab in application.material_identification_notebook.tabs()
        )
        self.assertEqual(labels, MATERIAL_IDENTIFICATION_STEP_LABELS)
        self.assertEqual(tuple(application.material_identification_pages), labels)

    def test_existing_tabs_remain_ordered_around_new_page(self):
        application = self._application()
        self.assertEqual(
            application.tabs.tabs(),
            (
                application.manual_review_tab,
                application.material_identification_tab,
                application.details_tab,
            ),
        )
        self.assertEqual(
            application.tabs.tab(application.manual_review_tab, "text"),
            "8. Manual review",
        )
        self.assertEqual(
            application.tabs.tab(application.details_tab, "text"),
            "10. Details",
        )

    def test_project_startup_builds_shell_without_backend(self):
        application = self._application()
        self.assertEqual(len(application.material_identification_pages), 7)
        self.assertFalse(hasattr(application, "material_identification_solver"))

    def test_variable_trace_callback_accepts_tk_arguments(self):
        application = self._application()

        mode, callback = application.abaqus_path.traces[0]

        self.assertEqual(mode, "write")
        callback("PY_VAR0", "", "write")

        def fail_refresh():
            raise RuntimeError("refresh failed")

        application._refresh_material_identification_pages = fail_refresh
        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            callback("PY_VAR0", "", "write")

    def test_project_evidence_page_renders_current_empty_states(self):
        application = self._application()
        displayed = {
            key: label.kwargs["text"]
            for key, label in application.material_identification_evidence_labels.items()
        }
        self.assertEqual(
            displayed,
            {
                "project": "Unsaved project",
                "fe_model": "Not selected",
                "experimental_data": "Not selected",
                "abaqus": "Unavailable — no launcher detected",
                "provenance": "Not validated — no modal comparison result",
            },
        )

    def test_task_definition_page_renders_supported_scope_and_interpretation(self):
        application = self._application()
        page = application.material_identification_pages["2. Task Definition"]
        text = "\n".join(_widget_texts(page))
        self.assertIn(
            "Effective homogeneous face-sheet property identification", text
        )
        for expected in ("Ex", "Ey", "Gxy", "Core", "Density", "Adhesive", "Geometry"):
            self.assertIn(f"• {expected}", text)
        self.assertIn("Effective homogeneous face-sheet properties", text)
        self.assertIn("not true fibre properties", text)
        self.assertIn("ply properties", text)
        self.assertIn("unique laminate constants", text)

    def test_modal_correspondence_page_renders_tables_and_scientific_wording(self):
        application = self._application()
        page = application.material_identification_pages["3. Modal Correspondence"]
        text = "\n".join(_widget_texts(page))
        self.assertIn("without new matching", text)
        self.assertIn("MAC/subspace are identity validation only", text)
        self.assertIn("not optimization objectives", text)
        self.assertEqual(
            tuple(application.material_correspondence_table.headings),
            ("experimental", "fe", "difference", "mac", "status"),
        )
        self.assertEqual(
            tuple(application.material_family_table.headings),
            ("family", "identity", "scalar", "subspace"),
        )

    def test_modal_correspondence_page_has_explicit_empty_state(self):
        application = self._application()
        self.assertEqual(
            application.material_correspondence_empty_label.kwargs["text"],
            "No comparison result available.",
        )
        self.assertEqual(application.material_correspondence_table.items, {})
        self.assertEqual(application.material_experimental_modes_table.items, {})
        self.assertEqual(application.material_fe_modes_table.items, {})
        self.assertEqual(application.material_family_table.items, {})

    def test_modal_correspondence_displays_existing_result_and_family_evidence(self):
        application = self._application()
        application.result = SimpleNamespace(
            experimental=SimpleNamespace(
                modes=(
                    SimpleNamespace(number=8, frequency_hz=99.0, metadata={}),
                    SimpleNamespace(number=9, frequency_hz=101.0, metadata={}),
                    SimpleNamespace(number=10, frequency_hz=140.0, metadata={}),
                )
            ),
            abaqus=SimpleNamespace(
                modes=(
                    SimpleNamespace(number=8, frequency_hz=100.0, metadata={}),
                    SimpleNamespace(number=9, frequency_hz=102.0, metadata={}),
                )
            ),
            pairs=(
                SimpleNamespace(
                    experimental_mode=8,
                    abaqus_mode=8,
                    frequency_error_percent=1.010101,
                    mac=0.97,
                    status="Accepted",
                ),
                SimpleNamespace(
                    experimental_mode=9,
                    abaqus_mode=9,
                    frequency_error_percent=0.990099,
                    mac=None,
                    status="Review",
                ),
            ),
            clusters=(
                SimpleNamespace(
                    fe_mode_ids=(8, 9),
                    experimental_mode_ids=(8, 9),
                    inclusion_status="included",
                    subspace_mac=0.992,
                ),
            ),
            metadata={},
        )

        application._refresh_material_identification_pages()

        self.assertEqual(
            tuple(application.material_experimental_modes_table.items.values()),
            (
                (8, "99", "Accepted"),
                (9, "101", "Review"),
                (10, "140", "Unpaired"),
            ),
        )
        self.assertEqual(
            tuple(application.material_correspondence_table.items.values()),
            (
                (8, 8, "+1.010", "0.970", "Accepted"),
                (9, 9, "+0.990", "—", "Review"),
            ),
        )
        self.assertEqual(
            tuple(application.material_family_table.items.values()),
            (("A8/A9 ↔ E8/E9", "PASS", "not forced", "available (subspace MAC 0.992)"),),
        )
        self.assertEqual(
            application.material_correspondence_empty_label.kwargs["text"], ""
        )

    def test_sensitivity_page_renders_required_sections_and_wording(self):
        application = self._application()
        page = application.material_identification_pages["4. Sensitivity"]
        text = "\n".join(_widget_texts(page))
        self.assertIn("Sensitivity indicates influence", text)
        self.assertIn("does not automatically mean identifiable material truth", text)
        for expected in (
            "Sensitivity matrix",
            "Observability summary",
            "Identifiability summary",
            "Core frozen",
            "Density frozen",
            "Adhesive frozen",
            "Geometry frozen",
        ):
            self.assertIn(expected, text)
        self.assertEqual(
            tuple(application.material_sensitivity_table.headings),
            ("observable", "type", "ex", "ey", "gxy"),
        )

    def test_sensitivity_page_has_explicit_empty_state(self):
        application = self._application()
        self.assertEqual(
            application.material_sensitivity_empty_label.kwargs["text"],
            "No sensitivity or identifiability evidence available.",
        )
        self.assertEqual(application.material_sensitivity_table.items, {})
        self.assertEqual(
            tuple(application.material_observability_table.items.values()),
            (("Ex", "unavailable"), ("Ey", "unavailable"), ("Gxy", "unavailable")),
        )
        self.assertEqual(
            tuple(application.material_identifiability_table.items.values()),
            (
                ("Rank", "Unavailable"),
                ("Condition number", "Unavailable"),
                ("Singular values", "Unavailable"),
                ("Weakest direction", "Unavailable"),
            ),
        )

    def test_sensitivity_page_displays_existing_evidence_without_recalculation(self):
        application = self._application()
        application.sensitivity_result = SimpleNamespace(
            observation_ids=("mode-8", "family-A8-A9"),
            observable_types={
                "mode-8": "scalar",
                "family-A8-A9": "family",
            },
            parameter_ids=("Ey", "Ex", "Gxy"),
            scaled_sensitivity=((0.2, 0.1, 0.3), (-0.5, 0.4, 0.0)),
        )
        application.identifiability_result = SimpleNamespace(
            rank=2,
            condition_number=125.0,
            singular_values=(4.0, 1.0, 0.032),
            parameter_observability={
                "Ex": "OBSERVABLE",
                "Ey": "PARTIALLY_OBSERVABLE",
                "Gxy": "UNOBSERVABLE",
            },
            deficient_directions=(
                SimpleNamespace(
                    parameter_loadings={"Ex": 0.7, "Ey": -0.714, "Gxy": 0.0}
                ),
            ),
        )

        application._refresh_material_identification_pages()

        self.assertEqual(
            tuple(application.material_sensitivity_table.items.values()),
            (
                ("mode-8", "Scalar mode", "0.1", "0.2", "0.3"),
                ("family-A8-A9", "Family observable", "0.4", "-0.5", "0"),
            ),
        )
        self.assertEqual(
            tuple(application.material_observability_table.items.values()),
            (("Ex", "strong"), ("Ey", "weak"), ("Gxy", "unavailable")),
        )
        self.assertEqual(
            tuple(application.material_identifiability_table.items.values()),
            (
                ("Rank", "2"),
                ("Condition number", "125"),
                ("Singular values", "4, 1, 0.032"),
                ("Weakest direction", "Ex +0.700, Ey -0.714, Gxy +0.000"),
            ),
        )
        self.assertEqual(application.material_sensitivity_empty_label.kwargs["text"], "")

    def test_identification_page_renders_interpretation_and_limitations(self):
        application = self._application()
        page = application.material_identification_pages["5. Identification"]
        text = "\n".join(_widget_texts(page))
        self.assertIn("Model U", text)
        self.assertIn("Model P", text)
        self.assertIn("U/P comparison", text)
        self.assertIn("Effective homogeneous face-sheet properties", text)
        self.assertIn("Not true fibre properties", text)
        self.assertIn("ply properties", text)
        self.assertIn("unique laminate constants", text)
        for limitation in (
            "Laminate architecture unknown",
            "Core frozen",
            "Density frozen",
            "Adhesive frozen",
            "Gxy weighting-sensitive",
        ):
            self.assertIn(limitation, text)

    def test_identification_page_has_explicit_empty_state(self):
        application = self._application()
        self.assertEqual(
            application.material_identification_empty_label.kwargs["text"],
            "No effective-property identification result available.",
        )
        unavailable_rows = (
            ("Ex", "—", "—"),
            ("Ey", "—", "—"),
            ("Gxy", "—", "—"),
        )
        self.assertEqual(
            tuple(application.material_model_u_table.items.values()), unavailable_rows
        )
        self.assertEqual(
            tuple(application.material_model_p_table.items.values()), unavailable_rows
        )
        self.assertEqual(
            application.material_identification_status_label.kwargs["text"],
            "NO_IDENTIFICATION_RESULT",
        )

    def test_identification_page_displays_stored_u_p_record(self):
        application = self._application()
        application.identified_properties = {
            "recommendation": "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
            "models": {
                "U": {
                    "properties_MPa": {
                        "Ex": 45927.2590467,
                        "Ey": 60716.9435522,
                        "Gxy": 8194.19208355,
                    }
                },
                "P": {
                    "properties_MPa": {
                        "Ex": 47854.4727274,
                        "Ey": 60291.0545452,
                        "Gxy": 6906.64847093,
                    }
                },
            },
            "stability": {
                "Ex": "RELATIVELY_STABLE",
                "Ey": "RELATIVELY_STABLE",
                "Gxy": "WEIGHTING_SENSITIVE",
                "U_P_symmetric_difference_percent": {
                    "Ex": 4.11,
                    "Ey": 0.704,
                    "Gxy": 17.053,
                },
            },
        }

        application._refresh_material_identification_pages()

        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (
                ("Ex", "45927.3", "MPa"),
                ("Ey", "60716.9", "MPa"),
                ("Gxy", "8194.19", "MPa"),
            ),
        )
        self.assertEqual(
            tuple(application.material_model_p_table.items.values()),
            (
                ("Ex", "47854.5", "MPa"),
                ("Ey", "60291.1", "MPa"),
                ("Gxy", "6906.65", "MPa"),
            ),
        )
        self.assertEqual(
            tuple(application.material_identification_comparison_table.items.values()),
            (
                ("Ex", "4.11", "relatively stable"),
                ("Ey", "0.704", "relatively stable"),
                ("Gxy", "17.053", "weighting-sensitive"),
            ),
        )
        self.assertEqual(
            application.material_identification_status_label.kwargs["text"],
            "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
        )
        self.assertEqual(application.material_identification_empty_label.kwargs["text"], "")

    def test_validation_page_renders_sections_badge_and_limitations(self):
        application = self._application()
        page = application.material_identification_pages["6. Validation"]
        text = "\n".join(_widget_texts(page))
        for expected in (
            "Overall validation status",
            "Primary observable validation",
            "Holdout validation",
            "NOT USED FOR IDENTIFICATION",
            "Effective properties only",
            "Laminate architecture unknown",
            "Core frozen",
            "Density frozen",
            "Adhesive frozen",
        ):
            self.assertIn(expected, text)
        self.assertEqual(
            tuple(application.material_primary_validation_table.headings),
            ("model", "observable", "experimental", "fe", "residual", "status"),
        )

    def test_validation_page_has_explicit_empty_state(self):
        application = self._application()
        self.assertEqual(
            application.material_validation_empty_label.kwargs["text"],
            "No validation evidence available.",
        )
        self.assertEqual(application.material_primary_validation_table.items, {})
        self.assertEqual(application.material_holdout_validation_table.items, {})
        self.assertEqual(
            application.material_validation_status_label.kwargs["text"],
            "NO_VALIDATION_EVIDENCE",
        )

    def test_validation_page_displays_stored_primary_and_holdout_rows(self):
        application = self._application()
        application.validation_evidence = {
            "recommendation": "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
            "validation_rows": (
                {
                    "model": "U",
                    "category": "PRIMARY",
                    "observable": "A7",
                    "experimental_value": 31.4234,
                    "FE_value": 29.787,
                    "equivalent_error_percent": -5.20756,
                    "identity_status": "PASS",
                },
                {
                    "model": "U",
                    "category": "HOLDOUT",
                    "observable": "A10+A11",
                    "experimental_value": 95.4542,
                    "FE_value": 95.4514,
                    "equivalent_error_percent": -0.002976,
                    "comparison_to_baseline": "IMPROVES",
                },
                {
                    "model": "P",
                    "category": "HOLDOUT",
                    "observable": "A13+A14",
                    "experimental_value": 209.127,
                    "FE_value": 205.864,
                    "equivalent_error_percent": -1.56029,
                    "comparison_to_baseline": "IMPROVES",
                },
                {
                    "model": "P",
                    "category": "HOLDOUT_DIAGNOSTIC",
                    "observable": "EXP10/A15 diagnostic",
                    "experimental_value": 228.607,
                    "FE_value": 229.56,
                    "equivalent_error_percent": 0.416883,
                    "identity_status": "DIAGNOSTIC_ONLY",
                },
            ),
        }

        application._refresh_material_identification_pages()

        self.assertEqual(
            tuple(application.material_primary_validation_table.items.values()),
            (("U", "A7", "31.4234", "29.787", "-5.20756", "PASS"),),
        )
        self.assertEqual(
            tuple(application.material_holdout_validation_table.items.values()),
            (
                ("U", "A10+A11", "95.4542", "95.4514", "-0.002976", "IMPROVES"),
                ("P", "A13+A14", "209.127", "205.864", "-1.56029", "IMPROVES"),
                (
                    "P",
                    "EXP10/A15 diagnostic",
                    "228.607",
                    "229.56",
                    "0.416883",
                    "DIAGNOSTIC_ONLY",
                ),
            ),
        )
        self.assertEqual(
            application.material_holdout_validation_badge.kwargs["text"],
            "NOT USED FOR IDENTIFICATION",
        )
        self.assertEqual(
            application.material_validation_status_label.kwargs["text"],
            "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
        )
        self.assertEqual(application.material_validation_empty_label.kwargs["text"], "")

    def test_report_page_renders_all_required_sections(self):
        application = self._application()
        page = application.material_identification_pages["7. Report"]
        text = "\n".join(_widget_texts(page))
        for expected in (
            "Project summary",
            "Task definition",
            "Effective homogeneous face-sheet property identification",
            "Unknown: Ex, Ey, Gxy",
            "Frozen: core, density, adhesive, geometry",
            "Identification result",
            "Validation evidence",
            "Effective properties only",
            "not ply/fibre constants",
            "unknown laminate architecture",
            "frozen core/interface assumptions",
            "Export PDF report",
            "Export JSON evidence",
            "Export CSV tables",
        ):
            self.assertIn(expected, text)

    def test_report_page_has_empty_state_and_disabled_exports(self):
        application = self._application()
        self.assertEqual(
            application.material_report_empty_label.kwargs["text"],
            "No stored identification or validation evidence available for report.",
        )
        for button in (
            application.material_report_pdf_button,
            application.material_report_json_button,
            application.material_report_csv_button,
        ):
            self.assertEqual(button.kwargs["state"], "disabled")
        self.assertEqual(
            tuple(application.material_report_project_table.items.values()),
            (
                ("Specimen / project", "Unsaved project"),
                ("FE model", "Not selected"),
                ("Experimental dataset", "Not selected"),
                ("Provenance status", "Not validated — no modal comparison result"),
            ),
        )

    def test_report_exports_become_available_with_stored_evidence(self):
        application = self._application_with_report_evidence()
        for button in (
            application.material_report_pdf_button,
            application.material_report_json_button,
            application.material_report_csv_button,
        ):
            self.assertEqual(button.kwargs["state"], "normal")
        self.assertEqual(application.material_report_empty_label.kwargs["text"], "")
        self.assertEqual(
            application.material_report_validation_status_label.kwargs["text"],
            "Validation status: ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
        )
        self.assertEqual(
            tuple(application.material_report_validation_table.items.values()),
            (
                ("PRIMARY", "U", "A7", "31.4", "29.8", "-5.2", "PASS"),
                (
                    "NOT USED FOR IDENTIFICATION",
                    "P",
                    "A10+A11",
                    "95.45",
                    "93.25",
                    "-2.3",
                    "IMPROVES",
                ),
            ),
        )

    def test_report_exporters_write_pdf_json_and_csv_from_snapshot(self):
        from material_identification_ui import (
            export_material_identification_csv,
            export_material_identification_json,
            export_material_identification_pdf,
            report_evidence_snapshot,
        )
        from pypdf import PdfReader

        application = self._application_with_report_evidence()
        snapshot = report_evidence_snapshot(application)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = export_material_identification_json(
                snapshot, root / "evidence.json"
            )
            csv_path = export_material_identification_csv(
                snapshot, root / "tables.csv"
            )
            pdf_path = export_material_identification_pdf(
                snapshot, root / "report.pdf"
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["validation"]["status"],
                "ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL",
            )
            with csv_path.open(newline="", encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(
                any(row["usage"] == "NOT USED FOR IDENTIFICATION" for row in rows)
            )
            reader = PdfReader(pdf_path)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Effective Material Identification Report", report_text)
            self.assertIn("ACCEPT_AS_ENGINEERING_EFFECTIVE_MODEL", report_text)


class ProjectEvidenceStatusTests(unittest.TestCase):
    def test_selected_and_validated_states_display_correctly(self):
        from material_identification_ui import project_evidence_status

        application = SimpleNamespace(
            project_path=Path("specimen-alpha.amcp.json"),
            abaqus_path=_FakeVariable(r"C:\models\panel.odb"),
            experimental_path=_FakeVariable(r"C:\tests\panel.unv"),
            abaqus_installation_label=_FakeVariable("Abaqus 2024"),
            _abaqus_installations={"Abaqus 2024": r"C:\SIMULIA\abaqus.bat"},
            result=SimpleNamespace(
                geometry=SimpleNamespace(
                    calibration_details={"provenance": "camera calibration record"}
                )
            ),
        )

        self.assertEqual(
            project_evidence_status(application),
            {
                "project": "specimen-alpha.amcp.json",
                "fe_model": "Selected — panel.odb",
                "experimental_data": "Selected — panel.unv",
                "abaqus": "Available — Abaqus 2024",
                "provenance": (
                    "Available — comparison result and calibration provenance loaded"
                ),
            },
        )


class MaterialIdentificationGuiShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk

            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk is unavailable: {error}")
        cls.root.withdraw()

        import main
        import ui_workflow

        disabled_recovery = {
            "autosave_enabled": False,
            "restore_on_startup": False,
            "show_recovery_notice": False,
        }
        with patch.object(
            ui_workflow,
            "load_recovery_preferences",
            return_value=disabled_recovery,
        ), patch.object(
            ui_workflow,
            "discover_abaqus_installations",
            return_value=(),
        ):
            cls.application = main.app.ModalComparatorApp(cls.root)
        cls.root.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            cls.root.destroy()

    def test_tab_creation_contains_all_gui_zero_sections(self):
        from ui_policy import MATERIAL_IDENTIFICATION_STEP_LABELS

        application = self.application
        self.assertIn(
            str(application.material_identification_tab),
            application.tabs.tabs(),
        )
        labels = tuple(
            application.material_identification_notebook.tab(tab, "text")
            for tab in application.material_identification_notebook.tabs()
        )
        self.assertEqual(labels, MATERIAL_IDENTIFICATION_STEP_LABELS)
        self.assertEqual(
            tuple(application.material_identification_pages),
            MATERIAL_IDENTIFICATION_STEP_LABELS,
        )

    def test_existing_tabs_remain_present_and_ordered(self):
        from ui_policy import FULL_TAB_LABELS, LayoutMode, responsive_layout_width

        application = self.application
        self.root.deiconify()
        try:
            application.ui_scale_percent.set(100)
            self.root.geometry("1600x900")
            self.root.update_idletasks()
            logical_width = responsive_layout_width(
                self.root.winfo_width(),
                float(self.root.tk.call("tk", "scaling")),
                application.ui_scale_percent.get(),
            )
            application._apply_responsive_layout()
            labels = tuple(
                application.tabs.tab(tab, "text")
                for tab in application.tabs.tabs()
            )

            self.assertGreaterEqual(logical_width, 1500)
            self.assertIs(application._layout_mode, LayoutMode.WIDE)
            self.assertEqual(labels, FULL_TAB_LABELS)
            self.assertEqual(len(labels), 10)
        finally:
            self.root.withdraw()

    def test_project_starts_without_identification_backend(self):
        application = self.application
        self.assertIsNone(application.result)
        self.assertFalse(application.running)
        self.assertEqual(len(application.material_identification_pages), 7)


if __name__ == "__main__":
    unittest.main()
