from datetime import datetime, timezone
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

from domain.evidence import (
    EvidenceProvenance,
    EvidenceScientificBinding,
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
)
from domain.identification_model import (
    EFFECTIVE_FACE_SHEET_MODEL,
    STAGE_A_BENDING_MODEL,
    IdentificationModelDefinition,
    IdentificationParameterDefinition,
    ModelWorkflowStatus,
)
from domain.material_identification_session import (
    MaterialIdentificationSession,
    MaterialIdentificationSourceIdentities,
    MaterialIdentificationTaskDefinition,
)
from domain.registration import FrozenRegistration
from scientific_state import calibration_fingerprint
from sp13_evidence_adapter import HISTORICAL_STATUS, SP13EvidenceBundle


TIMESTAMP = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
PROVENANCE = EvidenceProvenance(producer="material-identification UI test")
SOURCE = EvidenceSourceIdentity(
    source_id="synthetic-output",
    source_type="service-output",
    uri="project://synthetic/output",
    content_hash="4" * 64,
)


def _synthetic_historical_bundle() -> SP13EvidenceBundle:
    """Small synthetic UNBOUND bundle in the legacy historical SP13 layout.

    Presentation fixture only: the frozen-artifact loader is tested by
    test_sp13_evidence_adapter.  Values are synthetic, not REAL-4 results.
    """

    source = EvidenceSourceIdentity(
        source_id="synthetic/sp13_historical",
        source_type="frozen-sp13-artifact",
        uri="synthetic://sp13/historical",
        content_hash="5" * 64,
    )
    provenance = EvidenceProvenance(
        producer="synthetic historical SP13 view fixture",
        method="synthetic stand-in for read-only serialization of frozen artifacts",
        details={"specimen": "SP13", "historical_status": HISTORICAL_STATUS},
    )

    def record(record_type, name, status, content):
        return record_type.create(
            evidence_id=f"sp13-{name}-synthetic",
            timestamp=TIMESTAMP,
            source_identity=source,
            provenance=provenance,
            status=status,
            content=content,
            scientific_binding=None,
        )

    def svd(condition_number):
        return {
            "parameter_order": ("face_Ex", "face_Ey", "face_Gxy", "core_scale"),
            "singular_values": (4.0, 3.0, 2.0, 0.1),
            "numerical_rank": 4,
            "condition_number": condition_number,
            "weakest_right_singular_vector": (0.1, 0.2, 0.3, -0.9),
        }

    def validation_row(model, observable, category, experimental, fe, error, status):
        return {
            "model": model,
            "observable": observable,
            "category": category,
            "experimental_value": experimental,
            "FE_value": fe,
            "equivalent_error_percent": error,
            "identity_status": status,
        }

    return SP13EvidenceBundle(
        sensitivity=record(
            SensitivityEvidence,
            "sensitivity",
            "SYNTHETIC_FROZEN",
            {
                # CSV cells are stored as text in the historical layout.
                "raw_sensitivity_matrix": (
                    {"observable": "SYN_A1", "baseline_frequency_hz": "10.0",
                     "face_Ex": "0.125", "face_Ey": "0.25", "face_Gxy": "0.5",
                     "core_scale": "0.0625"},
                ),
            },
        ),
        identifiability=record(
            IdentifiabilityEvidence,
            "identifiability",
            "SYNTHETIC_FROZEN",
            {"models": {"U": svd(40.0), "P": svd(50.0)}},
        ),
        identification=record(
            IdentificationEvidence,
            "identification",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "identified_properties": {
                    "models": {
                        "U": {"properties_MPa": {"Ex": 41000.0, "Ey": 52000.0, "Gxy": 6100.0}},
                        "P": {"properties_MPa": {"Ex": 43000.0, "Ey": 51000.0, "Gxy": 7300.0}},
                    },
                    "stability": {
                        "Ex": "RELATIVELY_STABLE",
                        "Ey": "RELATIVELY_STABLE",
                        "Gxy": "WEIGHTING_SENSITIVE",
                        "U_P_symmetric_difference_percent": {"Ex": 5.0, "Ey": 2.0, "Gxy": 18.0},
                    },
                }
            },
        ),
        validation=record(
            ValidationEvidence,
            "validation",
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            {
                "validation_rows": (
                    validation_row("BASELINE", "SYN_A1", "PRIMARY", "10.0", "11.0", "10.0", "PASS"),
                    validation_row("U", "SYN_A1", "PRIMARY", "10.0", "10.5", "5.0",
                                   "mode 1; MAC=0.990000000; margin=0.900000000; PASS"),
                    validation_row("P", "SYN_H1", "HOLDOUT_DIAGNOSTIC", "30.0", "29.0", "-3.25",
                                   "local-family continuation mode 9; MAC=0.600000000; "
                                   "margin=0.300000000; DIAGNOSTIC_ONLY"),
                    validation_row("P", "SYN_A3_center", "HOLDOUT", "20.0", "19.5", "-2.5",
                                   "modes [3, 4]; min canonical correlation squared=0.990000000; "
                                   "max angle=1.000000 deg; PASS"),
                ),
            },
        ),
    )


def _registration():
    calibration = {"mode": "manual", "manual_scale": 1.0}
    return FrozenRegistration.create(
        experimental_source_identity={
            "path": "project/specimen/experiment.unv",
            "size": 4096,
            "mtime_ns": 1,
            "sha256": "1" * 64,
        },
        experimental_modal_set_identity=None,
        fe_geometry_identity={
            "schema_version": "fe-geometry-identity/2",
            "node_count": 2,
            "instances": ["PLATE-1"],
            "dof_components": ["U1", "U2", "U3"],
            "sha256": "2" * 64,
        },
        calibration=calibration,
        calibration_fingerprint=calibration_fingerprint(calibration),
        orientation_candidate_id="geometry-0123456789abcdef",
        rotation=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        translation=[0.0, 0.0, 0.0],
        coordinate_scales=[1.0, 1.0, 1.0],
        experimental_node_ids=[1, 2],
        mapped_fe_node_ids=["PLATE-1:1", "PLATE-1:2"],
        measured_dof_contract=[[False, False, True], [False, False, True]],
        registration_metrics={},
    )


REGISTRATION = _registration()

# A model the UI has never heard of: it must render without any UI change.
THIRD_MODEL = IdentificationModelDefinition.create(
    model_id="synthetic_spring_mass",
    display_name="Synthetic spring-mass test model",
    parameter_definitions=(
        IdentificationParameterDefinition(
            parameter_id="k1", display_name="k1", unit="N/m",
            meaning="Synthetic spring stiffness.",
        ),
        IdentificationParameterDefinition(
            parameter_id="m1", display_name="m1", unit="kg",
            meaning="Synthetic lumped mass.",
        ),
    ),
    frozen_assumptions=("Synthetic assumption: linear springs.",),
    limitations=("Synthetic limitation: test model only.",),
    workflow_status=ModelWorkflowStatus.RESEARCH,
)


def _session(model, specimen="SP14"):
    task = MaterialIdentificationTaskDefinition(
        model=model,
        selected_parameter_ids=model.parameter_ids,
        parameter_bounds={},
        weighting_selection="U",
        provenance=PROVENANCE,
    )
    return MaterialIdentificationSession.create(
        session_id=f"{model.model_id}-ui-session",
        created_at=TIMESTAMP,
        task_definition=task,
        source_identities=MaterialIdentificationSourceIdentities(specimen_label=specimen),
        registration=REGISTRATION,
    )


def _binding(session, **overrides):
    registration = session.registration_reference
    fields = {
        "identification_model_id": session.task_definition.identification_model_id,
        "identification_model_hash": session.task_definition.identification_model_hash,
        "identification_task_hash": session.task_definition.scientific_task_hash,
        "registration_hash": registration.registration_hash,
        "experimental_content_sha256": registration.experimental_content_sha256,
    }
    fields.update(overrides)
    return EvidenceScientificBinding.create(**fields)


def _bound(record_type, session, name, status, content, **overrides):
    return record_type.create(
        evidence_id=f"bound-{name}",
        timestamp=TIMESTAMP,
        source_identity=SOURCE,
        provenance=PROVENANCE,
        status=status,
        content=content,
        scientific_binding=_binding(session, **overrides),
    )


def _bound_sensitivity(session, parameter_ids, rows):
    # The shape the production runner stores.
    return _bound(
        SensitivityEvidence,
        session,
        "sensitivity",
        "COMPLETED",
        {
            "raw_sensitivity_matrix": tuple(
                {"observable": observable, "baseline_frequency_hz": 30.0}
                for observable, _values in rows
            ),
            "observation_ids": tuple(observable for observable, _values in rows),
            "parameter_ids": tuple(parameter_ids),
            "scaled_sensitivity": tuple(tuple(values) for _id, values in rows),
        },
    )


def _bound_identifiability(session, observability):
    return _bound(
        IdentifiabilityEvidence,
        session,
        "identifiability",
        "NOT_ASSESSED",
        {
            "models": {
                "U": {
                    "parameter_order": tuple(observability),
                    "singular_values": tuple(float(3 - index) for index in range(len(observability))),
                    "numerical_rank": len(observability),
                    "condition_number": 3.0,
                    "deficient_directions": (),
                    "parameter_observability": dict(observability),
                }
            }
        },
    )


def _bound_identification(session, values, unit, **overrides):
    # The committed adapter stores every model under "properties_MPa".
    return _bound(
        IdentificationEvidence,
        session,
        "identification",
        "COMPLETED",
        {
            "identified_properties": {
                "models": {
                    "U": {"properties_MPa": dict(values), "parameter_unit": unit, "uncertainty": {}}
                }
            }
        },
        **overrides,
    )


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


class _ApplicationHarness:
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
        # The M8.1 Auto-ID setup page builds real Tk widgets; the Tk shell tests and
        # tests/test_m8_auto_id_wizard.py cover it, so this fake-widget harness stubs it.
        with patch.object(material_identification_ui, "_INSTALLED", False), patch.object(
            material_identification_ui, "ttk", fake_ttk
        ), patch.object(material_identification_ui, "build_auto_id_setup_page", lambda app, page: None):
            material_identification_ui.install_material_identification_ui(app_module)
            return app_module.ModalComparatorApp(object())

    def _application_with_report_evidence(self):
        application = self._application()
        application.bind_material_identification_evidence(
            _synthetic_historical_bundle()
        )
        return application

    def _page_text(self, application, step_label):
        return "\n".join(
            _widget_texts(application.material_identification_pages[step_label])
        )

    def _all_texts(self, application):
        return "\n".join(_widget_texts(application.material_identification_tab))


class MaterialIdentificationInstallerTests(_ApplicationHarness, unittest.TestCase):
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
        self.assertEqual(len(application.material_identification_pages), 9)  # M8.1 adds "0. Auto-ID Setup"
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

    def test_data_readiness_page_has_explicit_empty_state(self):
        application = self._application()
        page = application.material_identification_pages[
            "2. Data Readiness Check"
        ]
        text = "\n".join(_widget_texts(page))
        self.assertIn("does not calculate corrections", text)
        self.assertIn("READY permits documented progression", text)
        self.assertEqual(
            application.material_readiness_status_label.kwargs["text"],
            "BLOCKED",
        )
        self.assertEqual(
            application.material_readiness_empty_label.kwargs["text"],
            "No data-readiness evidence available.",
        )
        self.assertEqual(
            tuple(application.material_readiness_experimental_table.items.values()),
            (
                ("Modal data available", "BLOCKED", "No stored readiness evidence"),
                ("Mode shapes available", "BLOCKED", "No stored readiness evidence"),
                ("Coordinates available", "BLOCKED", "No stored readiness evidence"),
                ("Registration status", "BLOCKED", "No stored readiness evidence"),
            ),
        )
        self.assertEqual(len(application.material_readiness_fe_table.items), 5)

    def test_data_readiness_page_renders_ready_state(self):
        application = self._application()
        application.data_readiness_evidence = {
            "overall_status": "READY",
            "experimental": {
                "modal_data": {"status": "READY", "detail": "7 fitted modes"},
                "mode_shapes": {"status": "READY", "detail": "121 points"},
                "coordinates": {"status": "READY", "detail": "Grid loaded"},
                "registration": {"status": "READY", "detail": "Frozen transform"},
            },
            "fe": {
                "model_files": {"status": "READY", "detail": "CAE/INP/ODB frozen"},
                "geometry_consistency": {"status": "READY", "detail": "Consistent"},
                "thickness_consistency": {"status": "READY", "detail": "Consistent"},
                "material_provenance": {"status": "READY", "detail": "Documented"},
                "adhesive_representation": {"status": "READY", "detail": "Documented"},
            },
        }

        application._refresh_material_identification_pages()

        self.assertEqual(
            application.material_readiness_status_label.kwargs["text"], "READY"
        )
        self.assertEqual(application.material_readiness_empty_label.kwargs["text"], "")
        self.assertEqual(
            tuple(application.material_readiness_experimental_table.items.values())[0],
            ("Modal data available", "READY", "7 fitted modes"),
        )
        self.assertEqual(
            tuple(application.material_readiness_fe_table.items.values())[-1],
            ("Adhesive representation status", "READY", "Documented"),
        )

    def test_data_readiness_page_renders_blocked_state(self):
        application = self._application()
        application.data_readiness_evidence = {
            "experimental": {
                "modal_data": {"status": "READY", "detail": "Available"},
                "mode_shapes": {"status": "READY", "detail": "Available"},
                "coordinates": {"status": "READY", "detail": "Available"},
                "registration": {
                    "status": "BLOCKED",
                    "detail": "Physical axes are not documented",
                },
            },
            "fe": {
                "model_files": {"status": "READY", "detail": "Available"},
                "geometry_consistency": {
                    "status": "WARNING",
                    "detail": "Review dimensions",
                },
                "thickness_consistency": {
                    "status": "BLOCKED",
                    "detail": "Core thickness conflict",
                },
                "material_provenance": {
                    "status": "WARNING",
                    "detail": "Layup unknown",
                },
                "adhesive_representation": {
                    "status": "BLOCKED",
                    "detail": "Mass conflict unresolved",
                },
            },
        }

        application._refresh_material_identification_pages()

        self.assertEqual(
            application.material_readiness_status_label.kwargs["text"],
            "BLOCKED",
        )
        self.assertIn(
            ("Registration status", "BLOCKED", "Physical axes are not documented"),
            tuple(application.material_readiness_experimental_table.items.values()),
        )
        self.assertIn(
            (
                "Adhesive representation status",
                "BLOCKED",
                "Mass conflict unresolved",
            ),
            tuple(application.material_readiness_fe_table.items.values()),
        )

    def test_task_definition_page_renders_supported_scope_and_interpretation(self):
        # The SP13 face-sheet wording belongs to the historical SP13 import only.
        application = self._application_with_report_evidence()
        page = application.material_identification_pages["3. Task Definition"]
        text = "\n".join(_widget_texts(page))
        self.assertIn(HISTORICAL_STATUS, text)
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
        page = application.material_identification_pages["4. Modal Correspondence"]
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
        page = application.material_identification_pages["5. Sensitivity"]
        text = "\n".join(_widget_texts(page))
        self.assertIn("Sensitivity indicates influence", text)
        self.assertIn("does not automatically mean identifiable material truth", text)
        for expected in (
            "Sensitivity matrix",
            "Observability summary",
            "Identifiability summary",
        ):
            self.assertIn(expected, text)
        # Nothing bound: no parameter columns and no SP13 frozen-parameter wording.
        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"], ("observable", "type")
        )
        self.assertNotIn("Core frozen", text)

        # The historical SP13 import keeps its legacy columns and wording.
        application.bind_material_identification_evidence(_synthetic_historical_bundle())
        text = "\n".join(_widget_texts(page))
        for expected in (
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
        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"],
            ("observable", "type", "ex", "ey", "gxy"),
        )

    def test_sensitivity_page_has_explicit_empty_state(self):
        application = self._application()
        self.assertEqual(
            application.material_sensitivity_empty_label.kwargs["text"],
            "No sensitivity or identifiability evidence available.",
        )
        self.assertEqual(application.material_sensitivity_table.items, {})
        # Nothing bound: no model, so no placeholder parameter rows.
        self.assertEqual(tuple(application.material_observability_table.items.values()), ())
        self.assertEqual(
            tuple(application.material_identifiability_table.items.values()),
            (
                ("Rank", "Unavailable"),
                ("Condition number", "Unavailable"),
                ("Singular values", "Unavailable"),
                ("Weakest direction", "Unavailable"),
            ),
        )

        # A historical import without identifiability keeps its legacy placeholders.
        bundle = _synthetic_historical_bundle()
        application.bind_material_identification_evidence(
            SP13EvidenceBundle(bundle.sensitivity, None, None, None)
        )
        self.assertEqual(
            tuple(application.material_observability_table.items.values()),
            (("Ex", "unavailable"), ("Ey", "unavailable"), ("Gxy", "unavailable")),
        )

    def test_sensitivity_page_displays_typed_historical_sp13_evidence(self):
        application = self._application()
        application.bind_material_identification_evidence(_synthetic_historical_bundle())

        self.assertEqual(
            tuple(application.material_sensitivity_table.items.values())[0],
            ("SYN_A1", "Scalar mode", "0.125", "0.25", "0.5"),
        )
        self.assertEqual(
            tuple(application.material_observability_table.items.values()),
            (("Ex", "unavailable"), ("Ey", "unavailable"), ("Gxy", "unavailable")),
        )
        summary = tuple(application.material_identifiability_table.items.values())
        self.assertEqual(summary[0], ("Rank", "U: 4; P: 4"))
        self.assertEqual(
            summary[1], ("Condition number", "U: 40; P: 50")
        )
        self.assertIn("core_scale -0.900", summary[3][1])
        self.assertEqual(application.material_sensitivity_empty_label.kwargs["text"], "")

    def test_identification_page_renders_interpretation_and_limitations(self):
        # The SP13 interpretation and limitations belong to the historical import.
        application = self._application_with_report_evidence()
        page = application.material_identification_pages["6. Identification"]
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
        # Nothing bound: no model, so no placeholder parameter rows.
        self.assertEqual(tuple(application.material_model_u_table.items.values()), ())
        self.assertEqual(tuple(application.material_model_p_table.items.values()), ())
        self.assertEqual(
            application.material_identification_status_label.kwargs["text"],
            "NO_IDENTIFICATION_RESULT",
        )

        # A historical import without identification keeps its legacy empty rows.
        unavailable_rows = (
            ("Ex", "—", "—"),
            ("Ey", "—", "—"),
            ("Gxy", "—", "—"),
        )
        bundle = _synthetic_historical_bundle()
        application.bind_material_identification_evidence(
            SP13EvidenceBundle(bundle.sensitivity, None, None, None)
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

    def test_identification_page_displays_typed_u_p_record(self):
        application = self._application()
        application.bind_material_identification_evidence(_synthetic_historical_bundle())

        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (
                ("Ex", "41000", "MPa"),
                ("Ey", "52000", "MPa"),
                ("Gxy", "6100", "MPa"),
            ),
        )
        self.assertEqual(
            tuple(application.material_model_p_table.items.values()),
            (
                ("Ex", "43000", "MPa"),
                ("Ey", "51000", "MPa"),
                ("Gxy", "7300", "MPa"),
            ),
        )
        self.assertEqual(
            tuple(application.material_identification_comparison_table.items.values()),
            (
                ("Ex", "5", "relatively stable"),
                ("Ey", "2", "relatively stable"),
                ("Gxy", "18", "weighting-sensitive"),
            ),
        )
        self.assertEqual(
            application.material_identification_status_label.kwargs["text"],
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
        )
        self.assertEqual(application.material_identification_empty_label.kwargs["text"], "")

    def test_validation_page_renders_sections_badge_and_limitations(self):
        application = self._application()
        page = application.material_identification_pages["7. Validation"]
        text = "\n".join(_widget_texts(page))
        for expected in (
            "Overall validation status",
            "Primary observable validation",
            "Holdout validation",
            "NOT USED FOR IDENTIFICATION",
        ):
            self.assertIn(expected, text)
        self.assertEqual(
            tuple(application.material_primary_validation_table.headings),
            ("model", "observable", "experimental", "fe", "residual", "status"),
        )
        self.assertNotIn("Laminate architecture unknown", text)

        # The SP13 model limitations belong to the historical import.
        application.bind_material_identification_evidence(_synthetic_historical_bundle())
        text = "\n".join(_widget_texts(page))
        for expected in (
            "Effective properties only",
            "Laminate architecture unknown",
            "Core frozen",
            "Density frozen",
            "Adhesive frozen",
        ):
            self.assertIn(expected, text)

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

    def test_validation_page_displays_typed_primary_and_holdout_rows(self):
        application = self._application()
        application.bind_material_identification_evidence(_synthetic_historical_bundle())

        primary = tuple(application.material_primary_validation_table.items.values())
        holdout = tuple(application.material_holdout_validation_table.items.values())
        self.assertIn(("U", "SYN_A1", "10", "10.5", "5", "mode 1; MAC=0.990000000; margin=0.900000000; PASS"), primary)
        self.assertIn(("P", "SYN_H1", "30", "29", "-3.25", "local-family continuation mode 9; MAC=0.600000000; margin=0.300000000; DIAGNOSTIC_ONLY"), holdout)
        self.assertEqual(
            application.material_holdout_validation_badge.kwargs["text"],
            "NOT USED FOR IDENTIFICATION",
        )
        self.assertEqual(
            application.material_validation_status_label.kwargs["text"],
            "SYNTHETIC_HISTORICAL_RECOMMENDATION",
        )
        self.assertEqual(application.material_validation_empty_label.kwargs["text"], "")

    def test_report_page_renders_all_required_sections(self):
        application = self._application()
        page = application.material_identification_pages["8. Report"]
        text = "\n".join(_widget_texts(page))
        for expected in (
            "Project summary",
            "Task definition",
            "Identification result",
            "Validation evidence",
            "Export PDF report",
            "Export JSON evidence",
            "Export CSV tables",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("Unknown: Ex, Ey, Gxy", text)

        # The SP13 task and limitation wording belongs to the historical import.
        application.bind_material_identification_evidence(_synthetic_historical_bundle())
        text = "\n".join(_widget_texts(page))
        for expected in (
            "Effective homogeneous face-sheet property identification",
            "Unknown: Ex, Ey, Gxy",
            "Frozen: core, density, adhesive, geometry",
            "Effective properties only",
            "not ply/fibre constants",
            "unknown laminate architecture",
            "frozen core/interface assumptions",
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
            "Validation status: SYNTHETIC_HISTORICAL_RECOMMENDATION",
        )
        rows = tuple(application.material_report_validation_table.items.values())
        self.assertIn(
            (
                "PRIMARY",
                "U",
                "SYN_A1",
                "10",
                "10.5",
                "5",
                "mode 1; MAC=0.990000000; margin=0.900000000; PASS",
            ),
            rows,
        )
        self.assertIn(
            (
                "NOT USED FOR IDENTIFICATION",
                "P",
                "SYN_A3_center",
                "20",
                "19.5",
                "-2.5",
                "modes [3, 4]; min canonical correlation squared=0.990000000; max angle=1.000000 deg; PASS",
            ),
            rows,
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
                "SYNTHETIC_HISTORICAL_RECOMMENDATION",
            )
            with csv_path.open(newline="", encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(
                any(row["usage"] == "NOT USED FOR IDENTIFICATION" for row in rows)
            )
            reader = PdfReader(pdf_path)
            report_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Effective Material Identification Report", report_text)
            self.assertIn("SYNTHETIC_HISTORICAL_RECOMMENDATION", report_text)


class ModelDrivenMaterialIdentificationUiTests(_ApplicationHarness, unittest.TestCase):
    """Production pages are driven by the session's IdentificationModelDefinition."""

    def stage_a_application(self, **evidence):
        application = self._application()
        session = _session(STAGE_A_BENDING_MODEL)
        application.bind_material_identification_session(session, **evidence)
        return application, session

    def stage_a_evidence(self, session):
        return {
            "sensitivity": _bound_sensitivity(
                session,
                ("D11", "D12", "D66"),
                (("EXP1_A7", (0.1, 0.2, 0.3)), ("EXP2_A9", (0.4, 0.5, 0.6))),
            ),
            "identifiability": _bound_identifiability(
                session,
                {"D11": "OBSERVABLE", "D12": "PARTIALLY_OBSERVABLE", "D66": "UNOBSERVABLE"},
            ),
            "identification": _bound_identification(
                session, {"D11": 12.0, "D12": 2.4, "D66": 5.0}, "N·m"
            ),
        }

    def assert_no_face_sheet_parameters(self, application):
        text = self._all_texts(application)
        for forbidden in ("• Ex", "• Gxy", "Unknown: Ex", "MPa", "Gxy weighting-sensitive",
                          "Laminate architecture unknown", "Core frozen", "face-sheet"):
            self.assertNotIn(forbidden, text)
        for table in (
            application.material_sensitivity_table,
            application.material_observability_table,
            application.material_model_u_table,
            application.material_model_p_table,
            application.material_identification_comparison_table,
            application.material_report_identification_table,
        ):
            for row in table.items.values():
                self.assertNotIn(row[0], ("Ex", "Ey", "Gxy"))
                self.assertNotIn("MPa", row)

    # A / B
    def test_stage_a_bound_session_renders_d11_d12_d66_in_newton_metres(self):
        application = self._application()
        session = _session(STAGE_A_BENDING_MODEL)
        application.bind_material_identification_session(
            session, **self.stage_a_evidence(session)
        )

        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"],
            ("observable", "type", "d11", "d12", "d66"),
        )
        self.assertEqual(
            tuple(
                application.material_sensitivity_table.headings[key]["text"]
                for key in ("d11", "d12", "d66")
            ),
            ("D11", "D12", "D66"),
        )
        self.assertEqual(
            tuple(application.material_sensitivity_table.items.values()),
            (
                ("EXP1_A7", "Scalar mode", "0.1", "0.2", "0.3"),
                ("EXP2_A9", "Scalar mode", "0.4", "0.5", "0.6"),
            ),
        )
        self.assertEqual(
            tuple(application.material_observability_table.items.values()),
            (("D11", "strong"), ("D12", "weak"), ("D66", "unavailable")),
        )
        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (("D11", "12", "N·m"), ("D12", "2.4", "N·m"), ("D66", "5", "N·m")),
        )
        self.assertEqual(
            tuple(application.material_report_identification_table.items.values())[0],
            ("D11", "12 N·m", "—", "—", "Unavailable"),
        )
        self.assert_no_face_sheet_parameters(application)

    # C
    def test_effective_face_bound_session_renders_ex_ey_gxy_in_mpa(self):
        application = self._application()
        session = _session(EFFECTIVE_FACE_SHEET_MODEL)
        application.bind_material_identification_session(
            session,
            sensitivity=_bound_sensitivity(
                session, ("Ex", "Ey", "Gxy"), (("EXP1_A7", (0.1, 0.2, 0.3)),)
            ),
            identification=_bound_identification(
                session, {"Ex": 45000.0, "Ey": 60000.0, "Gxy": 8000.0}, "MPa"
            ),
        )

        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"],
            ("observable", "type", "ex", "ey", "gxy"),
        )
        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (("Ex", "45000", "MPa"), ("Ey", "60000", "MPa"), ("Gxy", "8000", "MPa")),
        )
        text = self._page_text(application, "3. Task Definition")
        self.assertIn("Effective homogeneous face-sheet properties (effective_face_sheet)", text)
        self.assertIn("• Ex [MPa] — Effective homogeneous face-sheet modulus along X.", text)
        # The research model's own wording, not the historical SP13 conclusions.
        self.assertNotIn(HISTORICAL_STATUS, self._all_texts(application))
        self.assertNotIn("Gxy weighting-sensitive", self._all_texts(application))

    # D
    def test_an_unknown_third_model_renders_without_ui_changes(self):
        application = self._application()
        session = _session(THIRD_MODEL)
        application.bind_material_identification_session(
            session,
            sensitivity=_bound_sensitivity(session, ("k1", "m1"), (("SYN_1", (0.7, 0.3)),)),
            identification=_bound_identification(session, {"k1": 1500.0}, "N/m"),
        )

        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"],
            ("observable", "type", "k1", "m1"),
        )
        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (("k1", "1500", "N/m"), ("m1", "—", "—")),
        )
        text = self._page_text(application, "3. Task Definition")
        self.assertIn("• k1 [N/m] — Synthetic spring stiffness.", text)
        self.assertIn("• m1 [kg] — Synthetic lumped mass.", text)
        self.assertIn("Synthetic assumption: linear springs.", text)
        self.assert_no_face_sheet_parameters(application)

    # E
    def test_specimen_and_identification_model_are_distinct_concepts(self):
        application = self._application()
        # "SP13" is only a specimen label here; the model is Stage A.
        session = _session(STAGE_A_BENDING_MODEL, specimen="SP13")
        application.bind_material_identification_session(session)

        context = application.material_task_context_label.kwargs["text"]
        self.assertIn("Specimen / source: SP13", context)
        self.assertIn(
            "Identification model: Stage A plate bending stiffness (stage_a_bending)", context
        )
        self.assertIn(f"FrozenRegistration: {REGISTRATION.registration_hash}", context)
        self.assertNotIn(HISTORICAL_STATUS, context)

        from material_identification_ui import report_evidence_snapshot

        task = report_evidence_snapshot(application)["task_definition"]
        self.assertEqual(task["specimen"], "SP13")
        self.assertEqual(task["identification_model_id"], "stage_a_bending")
        self.assertEqual(task["identification_model_hash"], STAGE_A_BENDING_MODEL.definition_hash)
        self.assertEqual(task["registration_hash"], REGISTRATION.registration_hash)
        self.assertEqual(
            [item["parameter_id"] for item in task["unknown_parameters"]], ["D11", "D12", "D66"]
        )
        self.assert_no_face_sheet_parameters(application)

    # F
    def test_production_assumptions_and_limitations_come_from_the_model(self):
        application, _session_ = self.stage_a_application()
        texts = self._all_texts(application)
        for assumption in STAGE_A_BENDING_MODEL.frozen_assumptions:
            self.assertIn(assumption, application.material_task_frozen_label.kwargs["text"])
            self.assertIn(assumption, application.material_sensitivity_frozen_label.kwargs["text"])
        for limitation in STAGE_A_BENDING_MODEL.limitations:
            for label in (
                application.material_identification_limitations_label,
                application.material_validation_limitations_label,
                application.material_report_limitations_label,
            ):
                self.assertIn(limitation, label.kwargs["text"])

        from material_identification_ui import report_evidence_snapshot

        snapshot = report_evidence_snapshot(application)
        self.assertEqual(snapshot["limitations"], list(STAGE_A_BENDING_MODEL.limitations))
        for static_sp13 in ("Gxy weighting-sensitive", "Laminate architecture unknown",
                            "Core frozen", "Density frozen", "Adhesive frozen"):
            self.assertNotIn(static_sp13, texts)
        # workflow_status is not turned into a validation statement.
        self.assertNotIn("production", application.material_task_workflow_label.kwargs["text"])

    # G
    def test_historical_sp13_stays_historical_and_unbound(self):
        from material_identification_ui import material_identification_presentation

        application, _session_ = self.stage_a_application()
        bundle = _synthetic_historical_bundle()
        application.bind_material_identification_evidence(bundle)

        presentation = material_identification_presentation(application)
        self.assertEqual(presentation.kind, "historical")
        self.assertIsNone(presentation.model)
        self.assertIsNone(application.material_identification_session)
        self.assertIsNone(application.material_identification_evidence_view_model.model)
        self.assertEqual(presentation.specimen_label, "SP13")
        self.assertEqual(bundle.binding_status, "UNBOUND")
        self.assertIn(HISTORICAL_STATUS, application.material_identification_scope_label.kwargs["text"])
        context = application.material_task_context_label.kwargs["text"]
        self.assertIn("Specimen / source: SP13 (historical import)", context)
        self.assertIn(f"Identification model: not bound — {HISTORICAL_STATUS}", context)
        self.assertEqual(
            tuple(application.material_model_u_table.items.values())[0], ("Ex", "41000", "MPa")
        )

    # H
    def test_empty_stage_a_session_shows_its_model_not_ex_ey_gxy(self):
        application, _session_ = self.stage_a_application()

        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (("D11", "—", "—"), ("D12", "—", "—"), ("D66", "—", "—")),
        )
        self.assertEqual(
            tuple(application.material_observability_table.items.values()),
            (("D11", "unavailable"), ("D12", "unavailable"), ("D66", "unavailable")),
        )
        self.assertEqual(application.material_sensitivity_table.items, {})
        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"], ("observable", "type")
        )
        self.assert_no_face_sheet_parameters(application)

    # I
    def test_empty_effective_face_session_shows_its_selected_model_parameters(self):
        application = self._application()
        application.bind_material_identification_session(_session(EFFECTIVE_FACE_SHEET_MODEL))

        self.assertEqual(
            tuple(application.material_model_u_table.items.values()),
            (("Ex", "—", "—"), ("Ey", "—", "—"), ("Gxy", "—", "—")),
        )
        self.assertIn(
            "Identification model: Effective homogeneous face-sheet properties "
            "(effective_face_sheet)",
            application.material_task_context_label.kwargs["text"],
        )

    def test_nothing_bound_shows_a_neutral_state(self):
        application = self._application()
        self.assertIn("none selected", application.material_task_context_label.kwargs["text"])
        for table in (
            application.material_observability_table,
            application.material_model_u_table,
            application.material_model_p_table,
            application.material_identification_comparison_table,
            application.material_report_identification_table,
        ):
            self.assertEqual(table.items, {})
        self.assert_no_face_sheet_parameters(application)

    # J
    def test_identification_status_is_not_presented_as_validation(self):
        application = self._application()
        session = _session(STAGE_A_BENDING_MODEL)
        evidence = self.stage_a_evidence(session)
        application.bind_material_identification_session(
            session, identification=evidence["identification"]
        )

        page = self._page_text(application, "6. Identification")
        self.assertEqual(application.material_identification_status_label.kwargs["text"], "COMPLETED")
        self.assertIn("Stored identification status", page)
        self.assertNotIn("Stored validation state", page)
        self.assertIn("is not a validation of material properties", page)
        self.assertEqual(
            application.material_validation_status_label.kwargs["text"], "NO_VALIDATION_EVIDENCE"
        )
        texts = self._all_texts(application).lower()
        for claim in ("validated material", "material properties are validated",
                      "converged identification is validated"):
            self.assertNotIn(claim, texts)

    # K
    def test_sensitivity_subset_headers_match_only_rendered_parameters(self):
        application = self._application()
        session = _session(STAGE_A_BENDING_MODEL)
        application.bind_material_identification_session(
            session,
            sensitivity=_bound_sensitivity(session, ("D66", "D11"), (("EXP1_A7", (0.6, 0.1)),)),
        )

        self.assertEqual(
            application.material_sensitivity_table.kwargs["columns"],
            ("observable", "type", "d11", "d66"),
        )
        self.assertEqual(
            tuple(application.material_sensitivity_table.items.values()),
            (("EXP1_A7", "Scalar mode", "0.1", "0.6"),),
        )

    def test_session_binding_refuses_evidence_it_does_not_own(self):
        from material_identification_evidence_view import EvidenceModelBindingError

        application, session = self.stage_a_application()
        other_registration = _bound_identification(
            session, {"D11": 12.0}, "N·m", registration_hash="e" * 64
        )
        other_experiment = _bound_identification(
            session, {"D11": 12.0}, "N·m", experimental_content_sha256="f" * 64
        )
        for record in (other_registration, other_experiment):
            with self.subTest(record=record.scientific_binding):
                with self.assertRaisesRegex(ValueError, "different FrozenRegistration"):
                    application.bind_material_identification_session(
                        session, identification=record
                    )
        face_session = _session(EFFECTIVE_FACE_SHEET_MODEL)
        with self.assertRaises(EvidenceModelBindingError) as context:
            application.bind_material_identification_session(
                session,
                identification=_bound_identification(face_session, {"Ex": 1.0}, "MPa"),
            )
        self.assertEqual(context.exception.reason, "model_id")
        # Nothing was bound by the refused calls.
        self.assertIs(application.material_identification_session, session)
        self.assertIsNone(application.material_identification_evidence_view_model.identification)


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

    def test_selected_source_name_is_independent_of_host_path_flavour(self):
        # V7: on POSIX hosts pathlib.Path does not split on "\", so a Windows path
        # displayed whole. Simulate a POSIX host on any OS with PurePosixPath.
        from pathlib import PurePosixPath

        import material_identification_ui

        with patch.object(material_identification_ui, "Path", PurePosixPath):
            for value, expected in (
                (r"C:\models\panel.odb", "Selected — panel.odb"),
                (r"\\server\share\tests\panel.unv", "Selected — panel.unv"),
                ("/home/user/tests/panel.unv", "Selected — panel.unv"),
                ("C:/models/panel.odb", "Selected — panel.odb"),
                ("panel.odb", "Selected — panel.odb"),
                ("   ", "Not selected"),
            ):
                with self.subTest(value=value):
                    self.assertEqual(
                        material_identification_ui._selected_source_status(value),
                        expected,
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
        self.assertEqual(len(application.material_identification_pages), 9)  # M8.1 adds "0. Auto-ID Setup"


if __name__ == "__main__":
    unittest.main()
