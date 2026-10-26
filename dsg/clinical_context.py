"""DSG patient clinical context + MCP clinical-guidance handoff.

The Blender add-on stores *structured patient context without direct identifiers*.
It does not hard-code treatment recommendations.  Instead it creates a
country-aware guidance request for MCP, which must resolve current medication
information and professional/regulatory guidance from live authoritative
sources.  A sourced result can then be validated and stored back in the case.
"""
from __future__ import annotations

import logging as _dsg_logging
_DSG_LOG = _dsg_logging.getLogger(__name__)

import copy
import json
from pathlib import Path
from typing import Any

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import clinical_core
from . import core

PATIENT_STORE_KEY = "DSG_patient_clinical_context_json"
GUIDANCE_REQUEST_KEY = "DSG_clinical_guidance_request_json"
GUIDANCE_RESULT_KEY = "DSG_clinical_guidance_result_json"
CLINICAL_REVIEW_CONFIRMED_KEY = "DSG_clinical_review_confirmed"
CLINICAL_REVIEW_CONFIRMED_HASH_KEY = "DSG_clinical_review_confirmed_request_sha256"


def _registry_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / "clinical" / "source_registry.json"


def load_source_registry() -> dict[str, Any]:
    path = _registry_path()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != clinical_core.SOURCE_REGISTRY_SCHEMA:
        raise RuntimeError("Invalid clinical source registry schema")
    return data


def _load_scene_json(scene, key: str, default: Any):
    raw = str(scene.get(key, "") or "")
    if not raw:
        return copy.deepcopy(default)
    try:
        return json.loads(raw)
    except Exception:
        return copy.deepcopy(default)


def _store_scene_json(scene, key: str, value: Any):
    scene[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scene_del(scene, key: str):
    try:
        if key in scene:
            del scene[key]
    except Exception:
        _DSG_LOG.debug("suppressed exception", exc_info=True)


def empty_patient_context(country_code: str = "ES") -> dict[str, Any]:
    return clinical_core.normalize_patient_context({"country_code": country_code})


def get_patient_clinical_context(scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    raw = _load_scene_json(scene, PATIENT_STORE_KEY, empty_patient_context())
    return clinical_core.normalize_patient_context(raw)


def set_patient_clinical_context(payload: dict[str, Any], *, scene=None, replace: bool = True) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    previous = get_patient_clinical_context(scene)
    previous_hash = clinical_core.context_hash(previous)
    if replace:
        merged = dict(payload or {})
    else:
        merged = copy.deepcopy(previous)
        for key, value in dict(payload or {}).items():
            if key in {"medications", "conditions", "labs", "allergies"} and isinstance(value, list):
                merged[key] = list(value)
            else:
                merged[key] = value
    normalized = clinical_core.normalize_patient_context(merged)
    current_hash = clinical_core.context_hash(normalized)
    _store_scene_json(scene, PATIENT_STORE_KEY, normalized)
    # Only a material patient-context change invalidates sourced guidance.
    if current_hash != previous_hash:
        _scene_del(scene, GUIDANCE_REQUEST_KEY)
        _scene_del(scene, GUIDANCE_RESULT_KEY)
        scene[CLINICAL_REVIEW_CONFIRMED_KEY] = False
        scene[CLINICAL_REVIEW_CONFIRMED_HASH_KEY] = ""
    return normalized


def clear_patient_clinical_context(*, scene=None, country_code="ES") -> dict[str, Any]:
    scene = scene or bpy.context.scene
    ctx = empty_patient_context(country_code)
    _store_scene_json(scene, PATIENT_STORE_KEY, ctx)
    _scene_del(scene, GUIDANCE_REQUEST_KEY)
    _scene_del(scene, GUIDANCE_RESULT_KEY)
    scene[CLINICAL_REVIEW_CONFIRMED_KEY] = False
    scene[CLINICAL_REVIEW_CONFIRMED_HASH_KEY] = ""
    return ctx


def build_clinical_guidance_request(procedure: dict[str, Any], *, scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    context = get_patient_clinical_context(scene)
    request = clinical_core.build_guidance_request(context, procedure or {}, load_source_registry())
    _store_scene_json(scene, GUIDANCE_REQUEST_KEY, request)
    # A new request invalidates confirmation unless it is exactly the same request.
    confirmed_hash = str(scene.get(CLINICAL_REVIEW_CONFIRMED_HASH_KEY, "") or "")
    if confirmed_hash != str(request.get("request_sha256", "") or ""):
        scene[CLINICAL_REVIEW_CONFIRMED_KEY] = False
    return request


def get_clinical_guidance_request(*, scene=None) -> dict[str, Any] | None:
    scene = scene or bpy.context.scene
    data = _load_scene_json(scene, GUIDANCE_REQUEST_KEY, None)
    return data if isinstance(data, dict) else None


def apply_clinical_guidance_result(payload: dict[str, Any], *, scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    request = get_clinical_guidance_request(scene=scene)
    if not request:
        raise RuntimeError("Build a clinical guidance request before storing a guidance result")
    validated = clinical_core.validate_guidance_result(
        payload,
        expected_request_sha256=str(request.get("request_sha256", "") or ""),
        expected_country_code=str(request.get("country_code", "") or ""),
    )
    _store_scene_json(scene, GUIDANCE_RESULT_KEY, validated)
    scene[CLINICAL_REVIEW_CONFIRMED_KEY] = False
    scene[CLINICAL_REVIEW_CONFIRMED_HASH_KEY] = ""
    return validated


def get_clinical_guidance_result(*, scene=None) -> dict[str, Any] | None:
    scene = scene or bpy.context.scene
    data = _load_scene_json(scene, GUIDANCE_RESULT_KEY, None)
    return data if isinstance(data, dict) else None


def confirm_clinical_review(*, scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    request = get_clinical_guidance_request(scene=scene)
    result = get_clinical_guidance_result(scene=scene)
    if not request or not result:
        raise RuntimeError("A current sourced clinical guidance result is required before review confirmation")
    req_hash = str(request.get("request_sha256", "") or "")
    if req_hash != str(result.get("request_sha256", "") or ""):
        raise RuntimeError("Stored guidance result is stale for the current clinical request")
    scene[CLINICAL_REVIEW_CONFIRMED_KEY] = True
    scene[CLINICAL_REVIEW_CONFIRMED_HASH_KEY] = req_hash
    return {"confirmed": True, "request_sha256": req_hash}


def clinical_summary(*, scene=None) -> dict[str, Any]:
    scene = scene or bpy.context.scene
    context = get_patient_clinical_context(scene)
    request = get_clinical_guidance_request(scene=scene)
    result = get_clinical_guidance_result(scene=scene)
    ctx_hash = clinical_core.context_hash(context)
    request_hash = str((request or {}).get("request_sha256", "") or "")
    result_hash = str((result or {}).get("request_sha256", "") or "")
    confirmed = bool(scene.get(CLINICAL_REVIEW_CONFIRMED_KEY, False)) and bool(request_hash) and (
        str(scene.get(CLINICAL_REVIEW_CONFIRMED_HASH_KEY, "") or "") == request_hash
    )
    return {
        "schema": "dsg.clinical_summary.v1",
        "country_code": context["country_code"],
        "context_sha256": ctx_hash,
        "age_recorded": context.get("age") is not None,
        "medication_count": len(context.get("medications") or []),
        "condition_count": len(context.get("conditions") or []),
        "lab_count": len(context.get("labs") or []),
        "allergy_count": len(context.get("allergies") or []),
        "guidance_request_ready": bool(request),
        "guidance_result_ready": bool(result and result_hash == request_hash),
        "requires_clinician_review": bool((result or {}).get("requires_clinician_review", False)),
        "requires_medical_consultation": bool((result or {}).get("requires_medical_consultation", False)),
        "clinician_review_confirmed": confirmed,
        "guidance_status": str((result or {}).get("status", "NOT_RESOLVED") or "NOT_RESOLVED"),
        "request_sha256": request_hash,
    }


def get_country_source_registry(country_code: str) -> dict[str, Any]:
    registry = load_source_registry()
    code = clinical_core.normalize_country_code(country_code)
    countries = registry.get("countries") or {}
    result = {
        "schema": clinical_core.SOURCE_REGISTRY_SCHEMA,
        "country_code": code,
        "country": copy.deepcopy(countries.get(code) or {}),
        "eu_fallback": copy.deepcopy(countries.get("EU") or {}) if code in {"ES", "FR", "DE", "IT", "PT", "NL", "BE", "IE", "AT", "GR", "FI", "SE", "DK", "LU"} else {},
        "international_fallback": copy.deepcopy(countries.get("INT") or {}),
        "policy": copy.deepcopy(registry.get("policy") or {}),
    }
    if not result["country"]:
        result["country"] = {
            "label": "Unregistered country",
            "medication_resolver": "MCP_LIVE_LOOKUP",
            "sources": [],
            "discovery_required": True,
            "discovery_instruction": "Find the country's official medicine regulator, dental professional body, oral/maxillofacial society and national clinical guidance before advising.",
        }
    return result


def build_medication_lookup_request(term: str, country_code: str, *, scene=None) -> dict[str, Any]:
    term = str(term or "").strip()
    if not term:
        raise ValueError("Medication term is required")
    country = clinical_core.normalize_country_code(country_code)
    registry = get_country_source_registry(country)
    request = {
        "schema": "dsg.medication_lookup_request.v1",
        "country_code": country,
        "term": term,
        "patient_data_sent": False,
        "lookup": {
            "live_verification_required": True,
            "resolve": ["active_ingredient", "brand_name", "dose", "route", "authorization_status", "safety_notes"],
            "source_registry": registry,
        },
    }
    if country == "ES":
        request["lookup"]["preferred_adapter"] = "AEMPS_CIMA_REST"
        request["lookup"]["official_api"] = {
            "base": "https://cima.aemps.es/cima/rest/",
            "search_resource": "medicamentos",
            "search_parameters": {"nombre": term},
            "active_ingredient_parameter": "practiv1",
            "details_resource": "medicamento",
            "security_notes_resource": "notas/{nregistro}",
            "technical_sheet_html": "https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FichaTecnica.html",
        }
    else:
        request["lookup"]["preferred_adapter"] = "MCP_LIVE_OFFICIAL_LOOKUP"
    return request


class DSGClinicalProperties(PropertyGroup):
    country_code: StringProperty(name="País (ISO2)", default="ES", maxlen=2)
    age: IntProperty(name="Edad", default=0, min=0, max=125)
    smoking_status: EnumProperty(
        name="Tabaco",
        items=(("UNKNOWN", "No registrado", ""), ("NEVER", "Nunca", ""), ("FORMER", "Exfumador", ""), ("CURRENT", "Actual", "")),
        default="UNKNOWN",
    )
    previous_mronj: BoolProperty(name="MRONJ previa", default=False)
    head_neck_radiotherapy: BoolProperty(name="Radioterapia cabeza/cuello", default=False)

    medication_name: StringProperty(name="Medicamento", default="")
    medication_active: StringProperty(name="Principio activo", default="")
    medication_dose: StringProperty(name="Dosis", default="")
    medication_route: StringProperty(name="Vía", default="")
    medication_frequency: StringProperty(name="Frecuencia", default="")
    medication_indication: StringProperty(name="Indicación", default="")

    condition_name: StringProperty(name="Enfermedad/condición", default="")
    lab_name: StringProperty(name="Analítica", default="")
    lab_value: StringProperty(name="Valor", default="")
    lab_unit: StringProperty(name="Unidad", default="")
    lab_date: StringProperty(name="Fecha", default="")


class DSG_OT_ClinicalSaveBasics(Operator):
    bl_idname = "dsg.clinical_save_basics"
    bl_label = "Guardar datos básicos"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.dsg_clinical_props
        current = get_patient_clinical_context(context.scene)
        current.update({
            "country_code": props.country_code,
            "age": props.age if props.age > 0 else None,
            "smoking_status": props.smoking_status,
            "previous_mronj": props.previous_mronj,
            "head_neck_radiotherapy": props.head_neck_radiotherapy,
        })
        set_patient_clinical_context(current, scene=context.scene)
        self.report({"INFO"}, "Contexto clínico básico guardado")
        return {"FINISHED"}


class DSG_OT_ClinicalAddMedication(Operator):
    bl_idname = "dsg.clinical_add_medication"
    bl_label = "Añadir medicamento"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.dsg_clinical_props
        if not props.medication_name.strip() and not props.medication_active.strip():
            self.report({"ERROR"}, "Indica medicamento o principio activo")
            return {"CANCELLED"}
        current = get_patient_clinical_context(context.scene)
        meds = list(current.get("medications") or [])
        meds.append({
            "name": props.medication_name,
            "active_ingredient": props.medication_active,
            "dose": props.medication_dose,
            "route": props.medication_route,
            "frequency": props.medication_frequency,
            "indication": props.medication_indication,
        })
        current["medications"] = meds
        set_patient_clinical_context(current, scene=context.scene)
        props.medication_name = ""
        props.medication_active = ""
        props.medication_dose = ""
        props.medication_route = ""
        props.medication_frequency = ""
        props.medication_indication = ""
        self.report({"INFO"}, "Medicamento añadido")
        return {"FINISHED"}


class DSG_OT_ClinicalRemoveLastMedication(Operator):
    bl_idname = "dsg.clinical_remove_last_medication"
    bl_label = "Quitar último medicamento"
    bl_options = {"REGISTER"}

    def execute(self, context):
        current = get_patient_clinical_context(context.scene)
        meds = list(current.get("medications") or [])
        if meds:
            meds.pop()
            current["medications"] = meds
            set_patient_clinical_context(current, scene=context.scene)
        return {"FINISHED"}


class DSG_OT_ClinicalAddCondition(Operator):
    bl_idname = "dsg.clinical_add_condition"
    bl_label = "Añadir condición"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.dsg_clinical_props
        if not props.condition_name.strip():
            self.report({"ERROR"}, "Indica una enfermedad/condición")
            return {"CANCELLED"}
        current = get_patient_clinical_context(context.scene)
        conditions = list(current.get("conditions") or [])
        conditions.append({"name": props.condition_name})
        current["conditions"] = conditions
        set_patient_clinical_context(current, scene=context.scene)
        props.condition_name = ""
        return {"FINISHED"}


class DSG_OT_ClinicalAddLab(Operator):
    bl_idname = "dsg.clinical_add_lab"
    bl_label = "Añadir analítica"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.dsg_clinical_props
        if not props.lab_name.strip() or not props.lab_value.strip():
            self.report({"ERROR"}, "Indica nombre y valor")
            return {"CANCELLED"}
        current = get_patient_clinical_context(context.scene)
        labs = list(current.get("labs") or [])
        try:
            numeric = float(props.lab_value.replace(",", "."))
            item = {"name": props.lab_name, "value": numeric, "unit": props.lab_unit, "date": props.lab_date}
        except Exception:
            item = {"name": props.lab_name, "value_text": props.lab_value, "unit": props.lab_unit, "date": props.lab_date}
        labs.append(item)
        current["labs"] = labs
        set_patient_clinical_context(current, scene=context.scene)
        props.lab_name = props.lab_value = props.lab_unit = props.lab_date = ""
        return {"FINISHED"}


class DSG_OT_ClinicalCopyRequest(Operator):
    bl_idname = "dsg.clinical_copy_request"
    bl_label = "Copiar petición clínica MCP"
    bl_options = {"REGISTER"}

    def execute(self, context):
        procedure = {
            "procedure": "implant_surgery",
            "stage": "planning",
            "note": "UI-generated generic request; MCP should enrich with the actual planned procedure before advising.",
        }
        request = build_clinical_guidance_request(procedure, scene=context.scene)
        context.window_manager.clipboard = json.dumps(request, ensure_ascii=False, indent=2)
        self.report({"INFO"}, "Petición clínica copiada")
        return {"FINISHED"}


class DSG_OT_ClinicalConfirmReview(Operator):
    bl_idname = "dsg.clinical_confirm_review"
    bl_label = "Confirmar revisión clínica"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if core.reject_external_agent_for_user_gate(self, action=self.bl_idname):
            return {'CANCELLED'}
        try:
            confirm_clinical_review(scene=context.scene)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Revisión clínica confirmada por el clínico")
        return {"FINISHED"}


class DSG_OT_ClinicalClear(Operator):
    bl_idname = "dsg.clinical_clear"
    bl_label = "Borrar contexto clínico"
    bl_options = {"REGISTER"}

    def execute(self, context):
        clear_patient_clinical_context(scene=context.scene, country_code=context.scene.dsg_clinical_props.country_code)
        self.report({"INFO"}, "Contexto clínico borrado")
        return {"FINISHED"}


class DSG_PT_ClinicalContext(Panel):
    bl_idname = "DSG_PT_clinical_context"
    bl_label = "Paciente · Contexto clínico MCP"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DSG MCP"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.dsg_clinical_props
        summary = clinical_summary(scene=context.scene)
        context_data = get_patient_clinical_context(context.scene)

        box = layout.box()
        box.label(text="Sin nombre ni identificadores directos")
        row = box.row(align=True)
        row.prop(props, "country_code")
        row.prop(props, "age")
        box.prop(props, "smoking_status")
        box.prop(props, "previous_mronj")
        box.prop(props, "head_neck_radiotherapy")
        box.operator("dsg.clinical_save_basics", icon="CHECKMARK")

        med = layout.box()
        med.label(text=f"Medicaciones ({len(context_data.get('medications') or [])})")
        med.prop(props, "medication_name")
        med.prop(props, "medication_active")
        row = med.row(align=True)
        row.prop(props, "medication_dose")
        row.prop(props, "medication_route")
        med.prop(props, "medication_frequency")
        med.prop(props, "medication_indication")
        row = med.row(align=True)
        row.operator("dsg.clinical_add_medication", icon="ADD")
        row.operator("dsg.clinical_remove_last_medication", icon="REMOVE")
        for item in (context_data.get("medications") or [])[-4:]:
            label = item.get("active_ingredient") or item.get("name") or "Medicamento"
            med.label(text=label)

        cond = layout.box()
        cond.label(text=f"Condiciones ({len(context_data.get('conditions') or [])})")
        cond.prop(props, "condition_name")
        cond.operator("dsg.clinical_add_condition", icon="ADD")
        for item in (context_data.get("conditions") or [])[-4:]:
            cond.label(text=str(item.get("name", "")))

        lab = layout.box()
        lab.label(text=f"Analíticas ({len(context_data.get('labs') or [])})")
        lab.prop(props, "lab_name")
        row = lab.row(align=True)
        row.prop(props, "lab_value")
        row.prop(props, "lab_unit")
        lab.prop(props, "lab_date")
        lab.operator("dsg.clinical_add_lab", icon="ADD")

        status = layout.box()
        status.label(text=f"Guía: {summary['guidance_status']}")
        status.label(text=f"Fuentes verificadas: {'sí' if summary['guidance_result_ready'] else 'no'}")
        if summary["requires_medical_consultation"]:
            status.label(text="Consulta médica señalada por la guía", icon="ERROR")
        if summary["requires_clinician_review"] and not summary["clinician_review_confirmed"]:
            status.label(text="Revisión clínica pendiente", icon="ERROR")
        row = status.row(align=True)
        row.operator("dsg.clinical_copy_request", icon="COPYDOWN")
        row.operator("dsg.clinical_confirm_review", icon="CHECKMARK")
        layout.operator("dsg.clinical_clear", icon="TRASH")


_CLASSES = (
    DSGClinicalProperties,
    DSG_OT_ClinicalSaveBasics,
    DSG_OT_ClinicalAddMedication,
    DSG_OT_ClinicalRemoveLastMedication,
    DSG_OT_ClinicalAddCondition,
    DSG_OT_ClinicalAddLab,
    DSG_OT_ClinicalCopyRequest,
    DSG_OT_ClinicalConfirmReview,
    DSG_OT_ClinicalClear,
    DSG_PT_ClinicalContext,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dsg_clinical_props = PointerProperty(type=DSGClinicalProperties)


def unregister():
    if hasattr(bpy.types.Scene, "dsg_clinical_props"):
        del bpy.types.Scene.dsg_clinical_props
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            _DSG_LOG.debug("suppressed exception", exc_info=True)
